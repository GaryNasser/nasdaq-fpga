// Trace the failing CTRL=0x3 case cycle by cycle.
//
// Established by controlled experiment: CTRL=0x1 parses the stream, CTRL=0x3
// does not. Both set enable; only bit1 (soft reset) differs; data and timing are
// identical. Two theories were tried and discarded:
//
//   * TREADY dropping during the pulse - ruled out, beats=30/30 were accepted;
//   * gating enable across a two-cycle reset sequence - changed nothing.
//
// The reset must therefore leave some register in a state the CTRL=0x1 path never
// visits. Watching the state machine is the only way to find which.
//
// NOTE ON THE PREVIOUS TWO ATTEMPTS: both printed NO trace at all. The first put
// the observation loop inside the same fork/join as the driver, so it ran after
// everything had finished; the second gated on a flag that was set after the
// trace window. An empty trace looks exactly like "the design is idle" - that is
// how the absence nearly passed for a result. This version traces unconditionally
// from time 200 ns and prints a marker, so a missing trace is obvious.

`timescale 1ns / 1ps

`ifndef CTRL_VAL
`define CTRL_VAL 3
`endif

module tb_probe;

    reg         aclk = 0;
    reg         aresetn = 0;
    always #3.0 aclk = ~aclk;

    reg  [4:0]  s_axi_awaddr  = 0;
    reg         s_axi_awvalid = 0;
    wire        s_axi_awready;
    reg  [31:0] s_axi_wdata   = 0;
    reg  [3:0]  s_axi_wstrb   = 0;
    reg         s_axi_wvalid  = 0;
    wire        s_axi_wready;
    wire [1:0]  s_axi_bresp;
    wire        s_axi_bvalid;
    reg         s_axi_bready  = 1;
    reg  [4:0]  s_axi_araddr  = 0;
    reg         s_axi_arvalid = 0;
    wire        s_axi_arready;
    wire [31:0] s_axi_rdata;
    wire [1:0]  s_axi_rresp;
    wire        s_axi_rvalid;
    reg         s_axi_rready  = 1;

    reg  [63:0] s_axis_tdata  = 0;
    reg  [7:0]  s_axis_tkeep  = 0;
    reg         s_axis_tlast  = 0;
    reg         s_axis_tvalid = 0;
    wire        s_axis_tready;

    wire [7:0]  m_axis_tdata;
    wire        m_axis_tlast;
    wire        m_axis_tvalid;
    reg         m_axis_tready = 1;

    mold64_reasm #(
        .FIFO_AW (12),
        .SESSION (64'h4E41534441513031)
    ) dut (
        .aclk (aclk), .aresetn (aresetn),
        .s_axi_awaddr (s_axi_awaddr), .s_axi_awvalid (s_axi_awvalid),
        .s_axi_awready (s_axi_awready), .s_axi_wdata (s_axi_wdata),
        .s_axi_wstrb (s_axi_wstrb), .s_axi_wvalid (s_axi_wvalid),
        .s_axi_wready (s_axi_wready), .s_axi_bresp (s_axi_bresp),
        .s_axi_bvalid (s_axi_bvalid), .s_axi_bready (s_axi_bready),
        .s_axi_araddr (s_axi_araddr), .s_axi_arvalid (s_axi_arvalid),
        .s_axi_arready (s_axi_arready), .s_axi_rdata (s_axi_rdata),
        .s_axi_rresp (s_axi_rresp), .s_axi_rvalid (s_axi_rvalid),
        .s_axi_rready (s_axi_rready),
        .s_axis_tdata (s_axis_tdata), .s_axis_tkeep (s_axis_tkeep),
        .s_axis_tlast (s_axis_tlast), .s_axis_tvalid (s_axis_tvalid),
        .s_axis_tready (s_axis_tready),
        .m_axis_tdata (m_axis_tdata), .m_axis_tlast (m_axis_tlast),
        .m_axis_tvalid (m_axis_tvalid), .m_axis_tready (m_axis_tready)
    );

    localparam integer PKT_BYTES = 36;
    reg [7:0] img [0 : PKT_BYTES - 1];

    integer i, j, b, q, k;
    reg [63:0] wv;
    reg [31:0] CTRL_VALUE;
    integer rows = 0;

    always @(posedge aclk) begin
        if ($time >= 200 && rows < 120) begin
            $display("T %0t en=%b tready=%b st=%0d wr=%0d cm=%0d rd=%0d fne=%b bv=%b rxd=%b err=%0d",
                     $time, dut.enable, s_axis_tready, dut.state,
                     dut.pkt_wr_ptr, dut.bytes_committed, dut.pkt_rd_ptr,
                     dut.fifo_not_empty, dut.byte_valid_r,
                     dut.pkt_rx_done, dut.error_count);
            rows = rows + 1;
        end
    end

    task drive_all;
        begin
            q = 0;
            @(negedge aclk);
            while (q < PKT_BYTES) begin
                wv = 64'd0;
                b  = 0;
                for (j = 0; j < 8; j = j + 1) begin
                    if (q + j < PKT_BYTES) begin
                        wv[8*j +: 8] = img[q + j];
                        b = b + 1;
                    end
                end
                s_axis_tdata  = wv;
                s_axis_tkeep  = (b == 8) ? 8'hFF : ((8'hFF >> (8 - b)));
                s_axis_tlast  = ((q + b) >= PKT_BYTES);
                $display("SEND q=%0d b=%0d tkeep=%b tlast=%b", q, b, (b == 8) ? 8'hFF : ((8'hFF >> (8 - b))), ((q + b) >= PKT_BYTES));
                s_axis_tvalid = 1'b1;
                @(posedge aclk);
                while (!s_axis_tready) @(posedge aclk);
                @(negedge aclk);
                q = q + b;
            end
            s_axis_tvalid = 1'b0;
            s_axis_tkeep  = 8'h00;
            s_axis_tlast  = 1'b0;
        end
    endtask

    initial begin
        CTRL_VALUE = `CTRL_VAL;
        img[0] = 8'h4E; img[1] = 8'h41; img[2] = 8'h53; img[3] = 8'h44;
        img[4] = 8'h41; img[5] = 8'h51; img[6] = 8'h30; img[7] = 8'h31;
        img[8] = 8'h00; img[9] = 8'h00;
        img[10] = 8'h00; img[11] = 8'h02;
        for (i = 0; i < 2; i = i + 1) begin
            b = 12 + i*12;
            img[b+0] = 8'h00; img[b+1] = 8'h0A;
            img[b+2] = 8'h41;
            img[b+3] = 8'h00; img[b+4] = 8'h00; img[b+5] = 8'h00;
            img[b+6] = 8'h01; img[b+7] = 8'h00; img[b+8] = 8'h00;
            img[b+9] = 8'h02; img[b+10] = 8'h00; img[b+11] = 8'h03;
        end

        $display("CTRL=0x%0h, %0d-byte packet, 2 messages", CTRL_VALUE, PKT_BYTES);

        aresetn = 0;
        repeat (20) @(posedge aclk);
        aresetn = 1;
        repeat (10) @(posedge aclk);

        fork
            begin
                @(negedge aclk);
                s_axi_awaddr  = 5'h18;
                s_axi_awvalid = 1;
                s_axi_wdata   = CTRL_VALUE;
                s_axi_wstrb   = 4'hF;
                s_axi_wvalid  = 1;
                @(posedge aclk);
                while (!(s_axi_awready && s_axi_wready)) @(posedge aclk);
                @(negedge aclk);
                s_axi_awvalid = 0;
                s_axi_wvalid  = 0;
            end
            drive_all;
        join

        repeat (300) @(posedge aclk);
        $display("RESULT pkts=%0d msgs=%0d err=%0d",
                 dut.rx_packets, dut.rx_messages, dut.error_count);
        $finish;
    end

endmodule
